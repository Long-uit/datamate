"""
Unit tests cho Bước 6 — Entity linking:
1. Áp dụng khớp mờ (NFC, bỏ dấu, BM25 + Jaro-Winkler) cho tên hàng/khách/nhóm hàng.
2. Ngăn chặn false positive từ các từ dừng / thuật ngữ kinh doanh (bình quân, trung bình, hàng hóa, bị hủy, tháng, năm).
3. Hỗ trợ câu hỏi không dấu / teencode / biến thể quy cách:
   - "ma heo nuong nuoc mam" -> "Má heo nướng nước mắm"
   - "gas petrolimex 12kg" -> "Gas Petrolimex 12kg"
   - "banh croissant" -> "BÁNH CROISSANT"
   - "kem danh rang p/s 180g" -> "Kem đánh răng P/S 180 g"
4. Khớp nhóm hàng / danh mục (category):
   - "nhóm cát đá" -> "cát đá"
5. Không tìm được thực thể trong cơ sở dữ liệu thì từ chối (abstain).
"""

import pytest
from datamate.grounding_feasibility.entity_linker import (
    Candidate,
    link_entities,
    fuzzy_entity_match_score,
)
from datamate.output_abstention.abstention import compute_confidence_score


def test_stopword_suppression_in_entity_linking():
    """Từ dừng / thuật ngữ kinh doanh chung KHÔNG được khớp nhầm vào tên người / nhân viên / khách hàng."""
    candidates = [
        Candidate(value="Đặng Bình Quân", norm_value="đặng bình quân", entity_type="customer", source_table="khach_hang", source_col="Tên khách"),
        Candidate(value="Trịnh Thắng Huy", norm_value="trịnh thắng huy", entity_type="customer", source_table="khach_hang", source_col="Tên khách"),
        Candidate(value="Hàng hóa", norm_value="hàng hóa", entity_type="product", source_table="danh_muc", source_col="Loại hàng"),
    ]
    # Câu hỏi hỏi bình quân đơn: không được khớp khách Đặng Bình Quân
    matches_avg = link_entities("Tháng 6/2025 dthu bình quân mỗi đơn là bao nhiêu?", candidates=candidates)
    assert not any(m.matched_value == "Đặng Bình Quân" for m in matches_avg)

    # Câu hỏi hỏi đơn bị hủy: không được khớp khách Trịnh Thắng Huy
    matches_cancel = link_entities("so don bi huy trong thang 5 nam 2025 la bao nhieu z", candidates=candidates)
    assert not any(m.matched_value == "Trịnh Thắng Huy" for m in matches_cancel)


def test_fuzzy_matching_unaccented_and_teencode():
    """Khớp mờ NFC, bỏ dấu, Jaro-Winkler cho các tên hàng viết không dấu hoặc có biến thể khoảng trắng."""
    candidates = [
        Candidate(value="Má heo nướng nước mắm", norm_value="má heo nướng nước mắm", entity_type="product", source_table="thuc_don", source_col="Tên món"),
        Candidate(value="Gas Petrolimex 12kg", norm_value="gas petrolimex 12kg", entity_type="product", source_table="san_pham", source_col="Tên hàng"),
        Candidate(value="BÁNH CROISSANT", norm_value="bánh croissant", entity_type="product", source_table="san_pham", source_col="Tên hàng"),
        Candidate(value="Kem đánh răng P/S 180 g", norm_value="kem đánh răng p/s 180 g", entity_type="product", source_table="san_pham", source_col="Tên hàng"),
    ]

    # 1. Không dấu
    m1 = link_entities("so dia ma heo nuong nuoc mam ban duoc trong thang 11/2025", candidates=candidates)
    assert len(m1) > 0
    assert m1[0].matched_value == "Má heo nướng nước mắm"

    # 2. Gas Petrolimex
    m2 = link_entities("tiền bán gas petrolimex 12kg tháng 2/2026 là bn", candidates=candidates)
    assert len(m2) > 0
    assert m2[0].matched_value == "Gas Petrolimex 12kg"

    # 3. Viết hoa / thường
    m3 = link_entities("Cuối ngày hôm nay Bánh croissant còn mấy hộp chẵn", candidates=candidates)
    assert len(m3) > 0
    assert m3[0].matched_value == "BÁNH CROISSANT"

    # 4. Biến thể khoảng trắng '180g' vs '180 g'
    m4 = link_entities("hôm nay kho còn tồn bao nhiu hộp Kem đánh răng P/S 180g", candidates=candidates)
    assert len(m4) > 0
    assert m4[0].matched_value == "Kem đánh răng P/S 180 g"


def test_category_matching():
    """Khớp nhóm hàng / danh mục khi câu hỏi hỏi 'nhóm X' (Q14 cát đá)."""
    candidates = [
        Candidate(value="cát đá", norm_value="cát đá", entity_type="category", source_table="Danh sách hàng hóa", source_col="Nhóm hàng hóa"),
        Candidate(value="xi măng", norm_value="xi măng", entity_type="category", source_table="Danh sách hàng hóa", source_col="Nhóm hàng hóa"),
    ]
    matches = link_entities("Tỉ trọng của nhóm cát đá trong doanh thu tháng 8/2026 là bao nhiêu %?", candidates=candidates)
    assert len(matches) > 0
    assert matches[0].matched_value == "cát đá"
    assert matches[0].entity_type == "category"


def test_abstain_when_queried_entity_not_found():
    """Không tìm thấy thực thể được hỏi đích danh thì cổng tin cậy hạ điểm để abstain."""
    # Mặt hàng 'Trà sữa trân châu hoàng kim' không có trong CSDL cửa hàng
    candidates = [
        Candidate(value="Trà vải (L)", norm_value="trà vải (l)", entity_type="product", source_table="thuc_don", source_col="Tên món"),
        Candidate(value="Trà đào", norm_value="trà đào", entity_type="product", source_table="thuc_don", source_col="Tên món"),
    ]
    matches = link_entities("tiền bán Trà sữa trân châu hoàng kim tháng 3/2025 là bao nhiêu", candidates=candidates)
    assert len(matches) == 0

    # Cổng abstention phạt nặng câu hỏi hỏi thực thể nhưng không tìm thấy
    conf = compute_confidence_score(
        sub_ans={"type": "number", "answer": 0},
        question="tiền bán Trà sữa trân châu hoàng kim tháng 3/2025 là bao nhiêu",
        entity_matches=[],
        code_text="def solution(data):\n    return 0",
    )
    assert conf < 0.50, f"Confidence {conf} phải < 0.50 để kích hoạt abstain"
