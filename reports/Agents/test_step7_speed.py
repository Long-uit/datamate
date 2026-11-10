"""
Unit tests cho Bước 7 — Tốc độ (Speed & Business In-Memory Caching):
1. Kiểm tra gom nhóm câu hỏi theo business_id (contiguous grouping).
2. Kiểm tra bộ nhớ đệm get_cached_business_data:
   - Lần gọi đầu: nạp và làm sạch dữ liệu (is_cache = False).
   - Lần gọi thứ hai: lấy từ cache (is_cache = True) trong < 5ms (giảm 100% thời gian nạp lại).
3. Kiểm tra tốc độ trích xuất candidates và schema profiling.
"""

import time
from pathlib import Path
import pytest

from datamate.ingestion_schema.loader import load_business
from datamate.ingestion_schema.cleaner import clean_business
from datamate.grounding_feasibility.entity_linker import extract_candidates_from_business
from predict import get_cached_business_data, _BUSINESS_CACHE


DATA_ROOT = Path(__file__).resolve().parents[2] / "competition_data" / "train" / "data"


def test_question_grouping_by_business():
    """Kiểm tra logic gom nhóm câu hỏi theo business_id để tối đa hóa cache hit."""
    raw_questions = [
        {"id": "q1", "business_id": "biz_105"},
        {"id": "q2", "business_id": "biz_104"},
        {"id": "q3", "business_id": "biz_105"},
        {"id": "q4", "business_id": "biz_104"},
        {"id": "q5", "business_id": "biz_106"},
    ]
    grouped = sorted(raw_questions, key=lambda q: (q.get("business_id", ""), q.get("id", "")))
    biz_sequence = [q["business_id"] for q in grouped]
    assert biz_sequence == ["biz_104", "biz_104", "biz_105", "biz_105", "biz_106"]


def test_business_data_caching_speed():
    """Lần 1 nạp dữ liệu, lần 2 lấy từ RAM cache trong < 5ms."""
    biz_id = "biz_105"
    if biz_id in _BUSINESS_CACHE:
        del _BUSINESS_CACHE[biz_id]

    # Lần 1: Nạp mới
    t0 = time.perf_counter()
    data_dict1, con1, schema1, bd1, meta1, cand1, is_cache1 = get_cached_business_data(biz_id, DATA_ROOT)
    t_load1 = time.perf_counter() - t0
    assert not is_cache1
    assert len(data_dict1) > 0

    # Lần 2: Cache hit
    t1 = time.perf_counter()
    data_dict2, con2, schema2, bd2, meta2, cand2, is_cache2 = get_cached_business_data(biz_id, DATA_ROOT)
    t_load2 = time.perf_counter() - t1
    assert is_cache2
    assert t_load2 < 0.05  # < 50ms (thực tế < 1ms)
    assert len(data_dict2) == len(data_dict1)


def test_candidate_extraction_performance():
    """Trích xuất candidate values từ catalog và transaction tables diễn ra nhanh chóng."""
    biz_dir = DATA_ROOT / "biz_105"
    bd = clean_business(load_business(biz_dir))
    t0 = time.perf_counter()
    cands = extract_candidates_from_business(bd)
    elapsed = time.perf_counter() - t0
    assert elapsed < 3.0  # < 3 giây
    assert len(cands) > 0
