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
    "Tivi Sony Bravia 85 inch",
    "Xe đạp địa hình thể thao",
    "Bánh pizza nấm truffle",
    "Đồng hồ Rolex mạ vàng",
]

# Danh sách thuộc tính vô lý không có trong CSDL bán lẻ
MISSING_ATTRIBUTES = [
    "chiều cao trung bình của khách hàng",
    "nhiệt độ phòng lúc đặt hàng",
    "tâm trạng của nhân viên thu ngân",
    "màu sắc chiếc xe của người giao hàng",
    "chỉ số BMI của người mua",
    "quê quán của người thanh toán tiền",
    "tốc độ gió khi đơn hàng được giao",
]

UNANSWERABLE_CODE = """# Câu hỏi bất khả thi nằm ngoài phạm vi dữ liệu
def solution(dfs):
    return "unanswerable"
FINAL_RESULT = solution(dfs)
""".strip()


def generate_unanswerable_questions(
    business_id: str,
    as_of_date: str,
    date_range: tuple[str | None, str | None] = (None, None),
) -> list[dict[str, Any]]:
    """
    Sinh các cặp mẫu (question, target_answer, reason) thuộc nhóm Unanswerable.
    Mỗi mẫu kèm theo synthetic_code trả về 'unanswerable' để phục vụ huấn luyện SFT.
    """
    samples: list[dict[str, Any]] = []

    # 1. Hỏi ngoài phạm vi thời gian (Date out of range)
    future_years = [2028, 2029, 2030, 2032]
    past_years = [2015, 2017, 2018, 2019]
    far_future_year = random.choice(future_years)
    far_past_year = random.choice(past_years)
    month = random.randint(1, 12)

    future_templates = [
        f"Doanh thu của shop trong tháng {month} năm {far_future_year} là bao nhiêu?",
        f"Tổng số lượng sản phẩm bán được vào quý 2 năm {far_future_year}",
        f"Thống kê tiền bán hàng ngày 15 tháng {month} năm {far_future_year}",
    ]
    q_future = random.choice(future_templates)
    samples.append({
        "business_id": business_id,
        "as_of_date": as_of_date,
        "question": q_future,
        "type": "unanswerable",
        "reason": f"Kỳ hỏi năm {far_future_year} nằm hoàn toàn ngoài phạm vi dữ liệu",
        "synthetic_code": UNANSWERABLE_CODE,
        "answer": None,
    })

    past_templates = [
        f"Tổng số đơn hàng đã bán vào năm {far_past_year}",
        f"Doanh số bán ra trong tháng 5 năm {far_past_year} của cửa hàng",
        f"Liệt kê các đơn hàng giao thành công trong năm {far_past_year}",
    ]
    q_past = random.choice(past_templates)
    samples.append({
        "business_id": business_id,
        "as_of_date": as_of_date,
        "question": q_past,
        "type": "unanswerable",
        "reason": f"Kỳ hỏi năm {far_past_year} nằm ngoài phạm vi hoạt động của cửa hàng",
        "synthetic_code": UNANSWERABLE_CODE,
        "answer": None,
    })

    # 2. Hỏi sản phẩm hoàn toàn không tồn tại trong danh mục
    fake_product = random.choice(NON_EXISTENT_PRODUCTS)
    product_templates = [
        f"Sản phẩm {fake_product} bán được bao nhiêu cái trong tuần này?",
        f"Doanh thu của mặt hàng {fake_product} hôm nay là bao nhiêu tiền?",
        f"Có bao nhiêu khách hàng đã đặt mua {fake_product} trong tháng này?",
    ]
    q_product = random.choice(product_templates)
    samples.append({
        "business_id": business_id,
        "as_of_date": as_of_date,
        "question": q_product,
        "type": "unanswerable",
        "reason": f"Mặt hàng '{fake_product}' không có trong danh mục sản phẩm của shop",
        "synthetic_code": UNANSWERABLE_CODE,
        "answer": None,
    })

    # 3. Hỏi thông tin/thuộc tính không có trong CSDL
    missing_attr = random.choice(MISSING_ATTRIBUTES)
    attr_templates = [
        f"Thống kê {missing_attr} khi mua hàng hôm nay",
        f"Cho biết {missing_attr} của các đơn hàng trong tháng này",
    ]
    q_attr = random.choice(attr_templates)
    samples.append({
        "business_id": business_id,
        "as_of_date": as_of_date,
        "question": q_attr,
        "type": "unanswerable",
        "reason": f"Cơ sở dữ liệu không lưu trữ thông tin về {missing_attr}",
        "synthetic_code": UNANSWERABLE_CODE,
        "answer": None,
    })

    return samples
